'use client'
import { useEffect } from 'react'

const VAPID_PUBLIC_KEY = 'BBg07RSLW-kAvl5w76aJhXb9MlMr-OOhTTn6CvhpRERAAKzKy7n01vkzCcmy7bhhvaiJsgEMZ5Q3qI6d_C4z1DM'

function urlBase64ToUint8Array(b64: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (b64.length % 4)) % 4)
  const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const buf = new ArrayBuffer(raw.length)
  const view = new Uint8Array(buf)
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i)
  return view
}

export default function SwRegister() {
  useEffect(() => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return

    navigator.serviceWorker.register('/sw.js').then(async reg => {
      const existing = await reg.pushManager.getSubscription()
      if (existing) return

      const permission = await Notification.requestPermission()
      if (permission !== 'granted') return

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      })

      const json = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } }
      await fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
      })
    }).catch(() => {})
  }, [])

  return null
}
