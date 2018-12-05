const PRECACHE = 'precache_v35';

const PRECACHE_URLS = [
  '', // Alias for index.html
  'index.html',
  'static/bootstrap.min.css',
  'static/angular.min.1.7.5.js',
  'static/angular.min.1.7.5.js.map',
  'static/favicon.ico'
];

self.addEventListener('install', event => {
  console.log('install ' + PRECACHE);
  event.waitUntil(
    caches.open(PRECACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  console.log('activate ' + PRECACHE);
  const currentCaches = [PRECACHE];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return cacheNames.filter(cacheName => !currentCaches.includes(cacheName));
    }).then(cachesToDelete => {
      return Promise.all(cachesToDelete.map(cacheToDelete => {
        return caches.delete(cacheToDelete);
      }));
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  //console.log('fetch ' + PRECACHE + " " + event.request.url);

  if (event.request.url.startsWith(self.location.origin)) {
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        if (cachedResponse) {
          console.log('cachedResponse ' + event.request.url);
          return cachedResponse;
        }

        return fetch(event.request); // Do not cache API calls
      })
    );
  }
});

