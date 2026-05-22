export async function register() {
  if (process.env.NODE_ENV === "development") {
    const { EnvHttpProxyAgent, setGlobalDispatcher } = await import("undici")
    // NO_PROXY keeps localhost/127.x direct so Turbopack IPC/HMR is not routed through the proxy
    process.env.HTTP_PROXY = "http://127.0.0.1:10808"
    process.env.HTTPS_PROXY = "http://127.0.0.1:10808"
    process.env.NO_PROXY = "localhost,127.0.0.1,::1"
    setGlobalDispatcher(new EnvHttpProxyAgent())
  }
}
