var CACHE_NAME = 'uc-cleanup-v1';
var STATIC_URL = '{{ STATIC_URL }}';
var SHELL_FILES = [
  '/',
  STATIC_URL + 'css/palette.css',
  STATIC_URL + 'css/site.css',
  STATIC_URL + 'css/map.css',
  STATIC_URL + 'js/utils.js',
  STATIC_URL + 'js/base.js',
  STATIC_URL + 'js/map.js',
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(SHELL_FILES);
    }).catch(function() {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; }).map(function(k) {
          return caches.delete(k);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/accounts/')) {
    e.respondWith(
      fetch(e.request).catch(function() {
        return new Response(JSON.stringify({error: 'offline'}), {
          headers: {'Content-Type': 'application/json'},
          status: 503,
        });
      })
    );
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        return cached || fetch(e.request).then(function(response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) { cache.put(e.request, clone); });
          return response;
        });
      })
    );
    return;
  }
  e.respondWith(
    fetch(e.request).catch(function() {
      return caches.match(e.request).then(function(cached) {
        return cached || caches.match('/');
      });
    })
  );
});

self.addEventListener('sync', function(e) {
  if (e.tag === 'pending-reports') {
    e.waitUntil(
      self.clients.matchAll().then(function(clients) {
        clients.forEach(function(client) {
          client.postMessage({type: 'FLUSH_PENDING'});
        });
      })
    );
  }
});

self.addEventListener('push', function(e) {
  var data = {};
  if (e.data) {
    try { data = e.data.json(); } catch(err) {}
  }
  var title = data.title || 'UC CleanUp';
  var body = data.body || 'New activity nearby.';
  var url = data.url || '/';
  e.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: STATIC_URL + 'images/favicon.png',
      data: {url: url},
      badge: STATIC_URL + 'images/favicon.png',
    })
  );
});

self.addEventListener('notificationclick', function(e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    self.clients.matchAll({type: 'window'}).then(function(clients) {
      for (var i = 0; i < clients.length; i++) {
        if (clients[i].url === url && 'focus' in clients[i]) {
          return clients[i].focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(url);
      }
    })
  );
});
