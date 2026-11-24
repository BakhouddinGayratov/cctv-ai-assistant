import { ScanFace } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api } from "@/lib/api";

export function LoginPage() {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(login, password);
      location.assign("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <div className="app-backdrop" />
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-brand-gradient"><ScanFace className="size-5 text-white" /></span>
          <div>
            <h1 className="text-base font-semibold">CCTV AI</h1>
            <p className="text-xs text-fg-muted">Davom etish uchun tizimga kiring</p>
          </div>
        </div>
        <Field label="Login">
          <Input value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" autoCapitalize="none" autoFocus required />
        </Field>
        <Field label="Parol">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </Field>
        {error ? <p role="alert" className="text-xs text-critical">{error}</p> : null}
        <Button type="submit" variant="primary" className="w-full" loading={busy}>Kirish</Button>
      </form>
    </div>
  );
}
