// Retire the previous third-party advertising service worker.
// This worker does not load ads or import any external scripts.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await self.registration.unregister();
  })());
});
