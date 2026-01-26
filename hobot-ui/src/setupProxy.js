const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function (app) {
  app.use(
    ['/api', '/about'],
    createProxyMiddleware({
      target: 'http://localhost:8991',
      changeOrigin: true,
      logLevel: 'debug',
      onError: (err, req, res) => {
        console.error('[Proxy] Error occurred:', {
          message: err.message,
          code: err.code,
          syscall: err.syscall,
          address: err.address,
          port: err.port,
          stack: err.stack,
          requestUrl: req.url,
          requestMethod: req.method,
        });

        if (!res.headersSent) {
          res.status(500).json({
            detail: '프록시 서버 오류가 발생했습니다. 백엔드 서버가 실행 중인지 확인해주세요.',
            error: {
              message: err.message,
              code: err.code,
              address: err.address,
              port: err.port,
            }
          });
        }
      },
      onProxyReq: (proxyReq, req, res) => {
        console.log('[Proxy] Request:', {
          method: req.method,
          url: req.url,
          target: `http://localhost:8991${req.url}`,
          headers: req.headers,
        });
      },
      onProxyRes: (proxyRes, req, res) => {
        console.log('[Proxy] Response:', {
          statusCode: proxyRes.statusCode,
          statusMessage: proxyRes.statusMessage,
          url: req.url,
          headers: proxyRes.headers,
        });
      },
      onProxyReqWs: (proxyReq, req, socket) => {
        console.log('[Proxy] WebSocket request:', req.url);
      },
    })
  );
};

