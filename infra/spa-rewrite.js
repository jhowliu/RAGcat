// Only attached to the SPA behavior. API errors retain their original JSON/status.
function handler(event) {
  var request = event.request;
  var segment = request.uri.substring(request.uri.lastIndexOf('/') + 1);
  if (segment.indexOf('.') === -1) request.uri = '/index.html';
  return request;
}
