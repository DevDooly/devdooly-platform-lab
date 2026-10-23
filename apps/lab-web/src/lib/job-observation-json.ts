/** Job wire ingress: native JSON grammar and values, with decoded duplicate object keys rejected. */
export function parseJobObservationJson(text: string): unknown {
  const value: unknown = JSON.parse(text);
  const scopes: Array<Set<string> | null> = [];
  // Native parsing already proved balanced scopes and complete string tokens. Walk without recursion.
  for (let cursor = 0; cursor < text.length; cursor++) {
    const character = text[cursor];
    if (character === '{') scopes.push(new Set());
    else if (character === '[') scopes.push(null);
    else if (character === '}' || character === ']') scopes.pop();
    else if (character === '"') {
      const start = cursor++;
      while (text[cursor] !== '"') {
        if (text[cursor] === '\\') cursor++;
        cursor++;
      }
      let next = cursor + 1;
      while (next < text.length && /[\t\r\n ]/.test(text[next]!)) next++;
      // In valid JSON, only an object key string can be followed by a colon.
      if (text[next] === ':') {
        const key = JSON.parse(text.slice(start, cursor + 1)) as string;
        const keys = scopes.at(-1)!;
        if (keys.has(key)) throw new Error('INVALID_RECORD');
        keys.add(key);
      }
    }
  }
  return value;
}
