self.addEventListener('push', function (event) {
  let title = 'Cat of Wall Street'
  let body = 'New trade proposal — tap to review'
  let url = '/approvals'

  if (event.data) {
    try {
      const data = event.data.json()
      if (data.title) title = data.title
      if (data.body) body = data.body
      if (data.url) url = data.url
    } catch (_) {}
  }

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      data: { url },
      requireInteraction: true,
    })
  )
})

self.addEventListener('notificationclick', function (event) {
  event.notification.close()
  const url = event.notification.data?.url ?? '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      return clients.openWindow(url)
    })
  )
})
