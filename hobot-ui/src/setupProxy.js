const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8991',
      changeOrigin: true,
      logLevel: 'debug',
      onError: (err, req, res) => {
        console.error('Proxy error:', err);
        res.status(500).json({
          detail: '프록시 서버 오류가 발생했습니다. 백엔드 서버가 실행 중인지 확인해주세요.'
        });
      },
      onProxyReq: (proxyReq, req, res) => {
        console.log(`Proxying ${req.method} ${req.url} to http://localhost:8991${req.url}`);
      },
      onProxyRes: (proxyRes, req, res) => {
        console.log(`Proxy response: ${proxyRes.statusCode} for ${req.url}`);
      }
    })
  );
};

