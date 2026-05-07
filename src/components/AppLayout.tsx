import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../app/context";

const telegramChannelUrl = "https://t.me/Valensky1";
const supportUrl = "https://t.me/valenskymanager";

function shortName(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function AppLayout() {
  const { currentUser, logout } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const isLanding = location.pathname === "/";

  return (
    <div className="app-shell">
      <header className="topbar" aria-label="Главная навигация">
        <Link to="/" className="brand-mark" aria-label="На главную">
          <span>
            <strong>Менторство Валенского</strong>
            <small>{"контент -> Telegram -> продажи"}</small>
          </span>
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
        <strong className="footer-brand">Валенский</strong>
        <div className="footer-links">
          <span>Политика конфиденциальности</span>
          <span>Пользовательское соглашение</span>
          <a href={telegramChannelUrl} target="_blank" rel="noreferrer">
            Telegram-канал
          </a>
          <a href={supportUrl} target="_blank" rel="noreferrer">
            Поддержка
          </a>
        </div>
      </footer>
    </div>
  );
}
