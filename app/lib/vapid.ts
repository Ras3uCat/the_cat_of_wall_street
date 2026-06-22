function b64url(buf: Uint8Array): string {
  let s = ''
  for (let i = 0; i < buf.length; i++) s += String.fromCharCode(buf[i])
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

function decodeB64url(s: string): Uint8Array {
  const pad = s + '==='.slice((s.length + 3) % 4)
  const bin = atob(pad.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(bin, c => c.charCodeAt(0))
}

async function importKey(privateB64url: string, publicB64url: string): Promise<CryptoKey> {
  const pub = decodeB64url(publicB64url) // 65 bytes: 04 || x || y
  return crypto.subtle.importKey(
    'jwk',
    { kty: 'EC', crv: 'P-256', d: privateB64url, x: b64url(pub.slice(1, 33)), y: b64url(pub.slice(33)), ext: true },
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign'],
  )
}

async function makeJWT(endpoint: string, subject: string, key: CryptoKey): Promise<string> {
  const enc = new TextEncoder()
  const hdr = b64url(enc.encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })))
  const pay = b64url(enc.encode(JSON.stringify({
    aud: new URL(endpoint).origin,
    exp: Math.floor(Date.now() / 1000) + 43200,
    sub: subject,
  })))
  const sig = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, enc.encode(`${hdr}.${pay}`))
  return `${hdr}.${pay}.${b64url(new Uint8Array(sig))}`
}

export async function sendEmptyPush(
  sub: { endpoint: string },
  publicKey: string,
  privateKey: string,
  subject: string,
): Promise<{ ok: boolean; status: number }> {
  const key = await importKey(privateKey, publicKey)
  const jwt = await makeJWT(sub.endpoint, subject, key)
  const res = await fetch(sub.endpoint, {
    method: 'POST',
    headers: { Authorization: `vapid t=${jwt},k=${publicKey}`, TTL: '86400' },
  })
  return { ok: res.ok, status: res.status }
}
