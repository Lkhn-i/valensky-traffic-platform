import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useApp } from "../app/context";
import { LegalDocumentLinks } from "./ui";
import { footerLegalDocumentIds, legalDocuments, siteRequiredLegalDocumentIds } from "../domain/legal";

const telegramChannelUrl = "https://t.me/Valensky1";
const supportUrl = "https://t.me/valenskymanager";
const legalNoticeCookie = "valensky_legal_notice_v2";

function shortName(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function hasAcceptedLegalNotice() {
  if (typeof document === "undefined") {
    return true;
  }
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .some((part) => part === `${legalNoticeCookie}=accepted`);
}

function LegalNoticeBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(!hasAcceptedLegalNotice());
  }, []);

  if (!visible) {
    return null;
  }

  const acceptNotice = () => {
    document.cookie = `${legalNoticeCookie}=accepted; Path=/; Max-Age=31536000; SameSite=Lax`;
    setVisible(false);
  };

  return (
    <aside className="legal-notice" aria-label="Согласие с документами">
      <p>
        Для использования сайта нужно принять <LegalDocumentLinks documentIds={siteRequiredLegalDocumentIds} />. Оферта
        будет принята отдельно перед оплатой, согласие на рассылку остается необязательным.
      </p>
      <button className="chalk-button" type="button" onClick={acceptNotice}>
        Принимаю
      </button>
    </aside>
  );
}

export function AppLayout() {
  const { currentUser, logout } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const isLanding = location.pathname === "/";

  return (
    <div className="app-shell">
      <header className="topbar" aria-label="Главная навигация">
        <Link to="/" className="brand-mark" aria-label="Менторство Валенского">
          <img
            className="brand-image"
            src="/media/valensky-brand-board.png"
            alt="Менторство Валенского: контент, Telegram, продажи"
          />
        </Link>

        <nav className="top-nav">
          {currentUser ? (
            <>
              <NavLink to="/trainings">Тренинги</NavLink>
              {currentUser.role === "manager" ? <NavLink to="/manager/homeworks">Домашки</NavLink> : null}
              {currentUser.role === "admin" ? <NavLink to="/admin">Контент</NavLink> : null}
              <a href={supportUrl} target="_blank" rel="noreferrer">
                Поддержка
              </a>
            </>
          ) : (
            <>
              <a href="/#tariffs">Тарифы</a>
              <a href={supportUrl} target="_blank" rel="noreferrer">
                Поддержка
              </a>
            </>
          )}
        </nav>

        <div className="top-actions">
          {currentUser ? (
            <>
              <span className="user-chip" title={currentUser.email}>
                <span>{shortName(currentUser.name)}</span>
                {currentUser.name}
              </span>
              <button
                className="chalk-button ghost"
                type="button"
                onClick={() => {
                  void logout().then(() => navigate("/login"));
                }}
              >
                Выйти
              </button>
            </>
          ) : (
            <Link className="chalk-button" to="/login">
              Войти
            </Link>
          )}
        </div>
      </header>

      <main className={isLanding ? "main-area landing-area" : "main-area"}>
        <Outlet />
      </main>

      <footer className="site-footer">
        <img className="footer-brand-image" src="/media/valensky-footer-logo.png" alt="Валенский" />
        <div className="footer-links">
          {footerLegalDocumentIds.map((documentId) => (
            <a href={legalDocuments[documentId].url} target="_blank" rel="noreferrer" key={documentId}>
              {legalDocuments[documentId].title}
            </a>
          ))}
          <a href={telegramChannelUrl} target="_blank" rel="noreferrer">
            Telegram-канал
          </a>
          <a href={supportUrl} target="_blank" rel="noreferrer">
            Поддержка
          </a>
        </div>
      </footer>
      <LegalNoticeBanner />
    </div>
  );
}
