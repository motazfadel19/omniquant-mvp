/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false, // مهم لـ WebSocket (يمنع double mount)
};

export default nextConfig;