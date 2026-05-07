import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../app/context";

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
          <span className="brand-symbol">IV</span>
          <span>
            <strong>Менторство Валенского</strong>
            <small>{"контент -> Telegram -> продажи"}</small>
          </span>
        </Link>

        <nav className="top-nav">
          <NavLink to="/trainings">Тренинги</NavLink>
          {currentUser?.role === "manager" ? <NavLink to="/manager/homeworks">Домашки</NavLink> : null}
          {currentUser?.role === "admin" ? <NavLink to="/admin">Админка</NavLink> : null}
          <a href="https://t.me/valenskymanager" target="_blank" rel="noreferrer">
            Поддержка
          </a>
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
        <div>
          <strong>Менторство Валенского</strong>
          <p>Учебная среда в логике GetCourse, собранная как рабочая доска курса.</p>
        </div>
        <div className="footer-links">
          <Link to="/legal/privacy">Политика конфиденциальности</Link>
          <Link to="/legal/terms">Пользовательское соглашение</Link>
          <a href="https://t.me/Valensky1" target="_blank" rel="noreferrer">
            Telegram-группа
          </a>
          <a href="https://t.me/valenskymanager" target="_blank" rel="noreferrer">
            Поддержка
          </a>
        </div>
      </footer>
    </div>
  );
}
