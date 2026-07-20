import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/axios';

const TURNSTILE_SITE_KEY =
  import.meta.env.VITE_TURNSTILE_SITE_KEY || '1x00000000000000000000AA';

function SignupPage() {
  const turnstileRef = useRef(null);
  const turnstileWidgetId = useRef(null);
  const [turnstileToken, setTurnstileToken] = useState('');
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    org_name: '',
    intended_use: '',
  });
  const [pageStatus, setPageStatus] = useState('idle'); // idle | submitting | success | error
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const existingScript = document.getElementById('cf-turnstile-script');
    if (existingScript) {
      renderWidget();
      return;
    }

    const script = document.createElement('script');
    script.id = 'cf-turnstile-script';
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.defer = true;
    script.onload = renderWidget;
    document.head.appendChild(script);

    return () => {
      if (turnstileWidgetId.current != null && window.turnstile) {
        window.turnstile.remove(turnstileWidgetId.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function renderWidget() {
    if (!window.turnstile || !turnstileRef.current) return;
    turnstileWidgetId.current = window.turnstile.render(turnstileRef.current, {
      sitekey: TURNSTILE_SITE_KEY,
      callback: (token) => setTurnstileToken(token),
      'expired-callback': () => setTurnstileToken(''),
      'error-callback': () => setTurnstileToken(''),
    });
  }

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setPageStatus('submitting');
    setErrorMsg('');

    try {
      const resp = await api.post('/api/signups/', {
        ...form,
        cf_turnstile_response: turnstileToken,
      });
      if (resp.status === 200 || resp.status === 201) {
        setPageStatus('success');
      }
    } catch (err) {
      const detail = err.response?.data?.detail ?? 'Something went wrong. Please try again.';
      setErrorMsg(detail);
      setPageStatus('error');
      if (window.turnstile && turnstileWidgetId.current != null) {
        window.turnstile.reset(turnstileWidgetId.current);
        setTurnstileToken('');
      }
    }
  }

  if (pageStatus === 'success') {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center space-y-4">
            <p className="text-2xl font-bold text-foreground">Request received</p>
            <p className="text-sm text-muted-foreground">
              Thank you for your submission. We'll review your request and be in touch soon.
            </p>
            <Link to="/" className="text-sm text-primary underline underline-offset-2">
              Back to home
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-background">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="text-xl">Request access to Polaris Security</CardTitle>
          <p className="text-sm text-muted-foreground">
            Fill in the form below and our team will review your request.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Honeypot — hidden from real users */}
            <input
              type="text"
              name="website"
              autoComplete="off"
              tabIndex={-1}
              style={{ position: 'absolute', left: '-9999px' }}
              onChange={() => {}}
            />

            <div className="space-y-1.5">
              <Label htmlFor="full_name">Full name</Label>
              <Input
                id="full_name"
                name="full_name"
                value={form.full_name}
                onChange={handleChange}
                required
                disabled={pageStatus === 'submitting'}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Work email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
                disabled={pageStatus === 'submitting'}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="org_name">Organisation name</Label>
              <Input
                id="org_name"
                name="org_name"
                value={form.org_name}
                onChange={handleChange}
                required
                disabled={pageStatus === 'submitting'}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="intended_use">Intended use</Label>
              <Textarea
                id="intended_use"
                name="intended_use"
                rows={3}
                placeholder="Briefly describe how you plan to use the platform"
                value={form.intended_use}
                onChange={handleChange}
                required
                disabled={pageStatus === 'submitting'}
              />
            </div>

            <div ref={turnstileRef} />

            {pageStatus === 'error' && errorMsg && (
              <p className="text-sm text-destructive">{errorMsg}</p>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={pageStatus === 'submitting' || !turnstileToken}
            >
              {pageStatus === 'submitting' ? 'Submitting…' : 'Request access'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default SignupPage;
