/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for Cloudflare Pages (free). All routes are client
  // components; the two dynamic [jobId] routes read the jobId from the
  // live URL via useParams() and are pre-rendered once for a placeholder
  // param (see their generateStaticParams). The host rewrite in
  // public/_redirects serves that placeholder HTML for any /processing/*
  // or /result/* URL while keeping the real URL in the browser.
  output: "export",
};

export default nextConfig;
