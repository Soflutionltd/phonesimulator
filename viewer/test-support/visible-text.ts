// SPDX-License-Identifier: Apache-2.0
/**
 * Finds text a person would read written straight into the viewer's source, rather than said through `i18n.ts`.
 *
 * It reads a file's string literals -- joined where `+` or a template joins them, so markup is seen whole -- and
 * keeps what is not markup, a selector or a class list: two words in a row, a lone capitalised word, or a tooltip, an
 * accessible name or a placeholder written into a tag. It cannot know every string from every other -- a lone lower
 * case word is taken for a name the code uses -- so it is a net under the catalogue, not a proof.
 */
import ts from 'typescript'

/** Stands for whatever a template or a `+` puts between two pieces of text. */
const GAP = '\u0001'
const SAID_IN_TAGS = /\s(?:title|aria-label|placeholder|alt)="([^"]*)"/g
const WORD = /^[\p{L}’'`]{2,}[,.:;!?…]*$/u
const LABEL = /^\p{Lu}\p{Ll}+…?$/u

const isText = (node: ts.Node): node is ts.StringLiteral | ts.NoSubstitutionTemplateLiteral | ts.TemplateExpression =>
  ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateExpression(node)

const isJoin = (node: ts.Node): node is ts.BinaryExpression =>
  ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken

/** A literal's text, with a gap for each value put into it; a gap for anything that is not text. */
function textOf(node: ts.Node): string {
  if (ts.isParenthesizedExpression(node)) return textOf(node.expression)
  if (isJoin(node)) return textOf(node.left) + textOf(node.right)
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) return node.head.text + node.templateSpans.map((span) => GAP + span.literal.text).join('')
  return GAP
}

/** What of a piece of text a person would read: what is outside its tags, and what its tags say aloud. */
export function readable(text: string): string[] {
  const said: string[] = []
  const outside = text.replace(/<[^<>]*>/g, (tag) => {
    for (const [, value] of tag.matchAll(SAID_IN_TAGS)) said.push(value)
    return GAP
  })
  return [...outside.split(GAP), ...said.flatMap((value) => value.split(GAP))].map((part) => part.trim()).filter(Boolean)
}

/** Whether a readable piece is prose or a label, rather than a name the code uses. */
export function isProse(part: string): boolean {
  const tokens = part.split(/\s+/)
  if (tokens.length === 1) return LABEL.test(tokens[0])
  return tokens.some((token, index) => index > 0 && WORD.test(token) && WORD.test(tokens[index - 1]))
}

/** The pieces of prose written into a source file's literals, each once. */
export function proseIn(name: string, source: string): string[] {
  const file = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true)
  const found = new Set<string>()

  function visit(node: ts.Node): void {
    // What a module is imported from, and a type that is a literal, are names.
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node) || ts.isLiteralTypeNode(node)) return
    let above = node.parent
    while (above && ts.isParenthesizedExpression(above)) above = above.parent
    if ((isText(node) || isJoin(node)) && !(above && isJoin(above))) {
      for (const part of readable(textOf(node))) if (isProse(part)) found.add(part)
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return [...found]
}
