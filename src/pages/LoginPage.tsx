import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useApp } from "../app/context";
import { LegalConsent } from "../components/ui";

export function LoginPage() {
  const { login, currentUser } = useApp();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [legalAccepted, setLegalAccepted] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (currentUser) {
    const redirectTo =
      currentUser.role === "admin"
        ? "/admin"
        : currentUser.role === "manager"
          ? "/manager/homeworks"
          : "/trainings";
    return <Navigate to={redirectTo} replace />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!legalAccepted) {
      setError("Чтобы войти, нужно принять юридические документы и согласие на обработку данных.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      navigate(result.redirectTo || "/trainings");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="login-board">
      <form className="chalk-panel login-form" onSubmit={handleSubmit}>
        <span className="chalk-eyebrow">вход</span>
        <h1>Продолжить обучение</h1>
        <label>
          Логин или Email
          <input
            type="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setError("");
            }}
            autoComplete="username"
          />
        </label>
        <label>
          Пароль
          <input
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setError("");
            }}
            type="password"
            autoComplete="current-password"
          />
        </label>
        <LegalConsent
          id="login-legal-consent"
          checked={legalAccepted}
          onChange={(checked) => {
            setLegalAccepted(checked);
            setError("");
          }}
        />
        {error ? <p className="form-error">{error}</p> : null}
        <button className="chalk-button" type="submit" disabled={submitting || !legalAccepted}>
          {submitting ? "Входим..." : "Войти"}
        </button>
        <div className="login-links">
          <Link to="/">Вернуться к тарифам</Link>
          <a href="https://t.me/valenskymanager" target="_blank" rel="noreferrer">
            Поддержка в Telegram
          </a>
        </div>
      </form>
    </section>
  );
}
