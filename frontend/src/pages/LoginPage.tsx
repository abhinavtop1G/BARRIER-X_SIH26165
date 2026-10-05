import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google'
import { useAuth } from '@/context/AuthContext'
import { getHealth } from '@/api/client'

export default function LoginPage() {
  const { loginWithGoogle, loginAsDemo } = useAuth()
  const navigate            = useNavigate()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)
  const [demoAvailable, setDemoAvailable] = useState(false)

  useEffect(() => {
    let active = true
    getHealth().then(h => { if (active) setDemoAvailable(h.demo_login) })
    return () => { active = false }
  }, [])

  async function onDemo() {
    setLoading(true)
    setErrorMsg(null)
    try {
      await loginAsDemo()
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      setErrorMsg(err?.message ?? 'Demo login failed')
    } finally {
      setLoading(false)
    }
  }

  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  async function onSuccess(res: CredentialResponse) {
    if (res.credential) {
      setLoading(true)
      setErrorMsg(null)
      try {
        await loginWithGoogle(res.credential)
        navigate('/dashboard', { replace: true })
      } catch (err: any) {
        setErrorMsg(err?.message ?? 'Google OAuth authentication failed')
      } finally {
        setLoading(false)
      }
    } else {
      setErrorMsg('Google did not provide a valid ID credential.')
    }
  }

  function onError() {
    setErrorMsg('Google Sign-In failed or popup was closed. Please try again.')
  }

  return (
    <div className="min-h-dvh bg-bx-bg grid lg:grid-cols-2">

      <div className="hidden lg:flex flex-col justify-between p-14 bg-[#050505] border-r border-bx-border relative overflow-hidden">
        <div className="absolute -bottom-32 -left-32 w-80 h-80 bg-bx-gold/[0.05] rounded-full blur-[100px] pointer-events-none" />

        <div className="font-display text-2xl font-bold tracking-widest uppercase">
          BARRIER <span className="text-bx-gold">X</span>
        </div>

        <div className="max-w-sm">
          <h2 className="font-display text-4xl font-bold leading-tight text-bx-text mb-5">
            Safety Intelligence<br />Platform
          </h2>
          <p className="text-bx-secondary leading-relaxed mb-8">
            AI-powered SIF potential analysis for Oil India Limited HSSE operations.
            Surfaces high-consequence reports so HSE teams act before a serious event.
          </p>
          <p className="text-sm text-bx-muted italic border-l-2 border-bx-subtle pl-4 leading-relaxed">
            A triage aid that ranks reports for human review.
            It does not replace human judgment.
          </p>
        </div>

        <p className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-muted">
          Oil India Limited · HSSE Operations
        </p>
      </div>

      <div className="flex items-center justify-center p-8 lg:p-14">
        <div className="w-full max-w-sm flex flex-col items-center text-center">

          <div className="lg:hidden font-display text-2xl font-bold tracking-widest uppercase mb-10">
            BARRIER <span className="text-bx-gold">X</span>
          </div>

          <h3 className="font-display text-3xl font-bold text-bx-text mb-2">Sign In</h3>
          <p className="text-sm text-bx-secondary mb-8 max-w-[32ch]">
            Access the BARRIER X safety intelligence platform using your Google account.
          </p>

          {errorMsg && (
            <div className="w-full mb-6 p-3.5 rounded-lg bg-red-900/20 border border-red-900/40 text-red-400 text-xs text-left">
              <span className="font-semibold block mb-0.5">Authentication Error:</span>
              {errorMsg}
            </div>
          )}

          {demoAvailable && (
            <div className="w-full mb-6">
              <button
                type="button"
                onClick={onDemo}
                disabled={loading}
                className="w-full py-3 rounded-lg bg-bx-gold text-black font-semibold text-sm hover:opacity-90 transition disabled:opacity-50"
              >
                Continue as demo judge
              </button>
              <p className="mt-2 text-[0.7rem] text-bx-muted">
                Evaluation access without a Google account. Enabled by the gateway's DEMO_MODE setting.
              </p>
            </div>
          )}

          {!googleClientId && !demoAvailable && (
            <div className="w-full mb-6 p-3.5 rounded-lg bg-bx-gold/10 border border-bx-gold/30 text-bx-gold text-xs text-left">
              <span className="font-semibold block mb-0.5">Notice:</span>
              Configure <code className="font-mono bg-black/40 px-1 py-0.5 rounded">VITE_GOOGLE_CLIENT_ID</code> in <code className="font-mono bg-black/40 px-1 py-0.5 rounded">frontend/.env</code> to connect your Google Cloud Console OAuth App.
            </div>
          )}

          <div className="w-full flex justify-center mb-6">
            {loading ? (
              <div className="text-xs text-bx-secondary py-3">Verifying Google credential with Gateway...</div>
            ) : (
              <GoogleLogin
                onSuccess={onSuccess}
                onError={onError}
                theme="filled_black"
                size="large"
                shape="rectangular"
                width="320"
                text="signin_with"
              />
            )}
          </div>

          <div className="mt-8 pt-6 border-t border-bx-border w-full">
            <p className="text-xs text-bx-muted leading-relaxed text-center">
              Authentication is governed by Google OAuth 2.0. Credentials and session tokens
              are verified server-side via the Go API Gateway.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
