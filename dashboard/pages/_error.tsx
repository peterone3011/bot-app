// Minimal Pages Router error page — overrides Next.js default to avoid
// prerender failures caused by its internal hook usage.
function Error({ statusCode }: { statusCode?: number }) {
  return <p>{statusCode ? `Error ${statusCode}` : "An error occurred"}</p>
}

Error.getInitialProps = ({ res, err }: { res?: { statusCode: number }; err?: { statusCode: number } }) => {
  const statusCode = res ? res.statusCode : err ? err.statusCode : 404
  return { statusCode }
}

export default Error
