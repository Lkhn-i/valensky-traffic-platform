import { Link } from "react-router-dom";
import { useApp } from "../app/context";
import { ChalkTitle } from "../components/ui";
import { mainModuleCatalog } from "../domain/catalog";

export function HomePage() {
  const { state } = useApp();
  const tariffs = [...state.tariffs].sort((left, right) => left.sortOrder - right.sortOrder);

  return (
    <>
      <section className="hero-board">
        <div className="hero-copy">
          <span className="chalk-eyebrow">учебная платформа</span>
          <h1>Личный бренд через контент, Telegram и измеримую монетизацию</h1>
          <p>
            От хаотичных публикаций к системе: контент, воронка, оффер, продажи и масштабирование.
            Внутри все разложено как на доске: уроки, материалы, домашки, доступы и проверка.
          </p>
          <div className="action-row hero-actions">
            <Link className="chalk-button" to="/login">
              Войти
            </Link>
            <a className="chalk-button ghost" href="https://t.me/Valensky1" target="_blank" rel="noreferrer">
              Telegram-канал
            </a>
          </div>
        </div>

        <div className="hero-visual">
          <div className="chalk-diagram" aria-label="Маршрут курса">
            <span>личный бренд</span>
            <i />
            <span>контентная система</span>
            <i />
            <span>Telegram</span>
            <i />
            <span>оффер</span>
            <i />
            <span>продажи</span>
          </div>
          <div className="hero-side-figure" aria-hidden="true" />
        </div>
      </section>

      <section className="board-section">
        <ChalkTitle
          eyebrow="что собираем"
          title="Не курс про ролики, а рабочая система роста"
          text="Короткое видео, AI-production, social search, Telegram, paid amplification и аналитика работают как части одного маршрута."
        />
        <div className="feature-grid">
          {[
            ["Позиционирование", "Один сегмент, одна боль, один понятный угол и причина подписки."],
            ["Контент", "Банк идей, первые публикации, формулы роликов и AI-редактура без AI-slop."],
            ["Telegram", "Посадочный пост, продуктовая среда, лид-магнит, оффер и первый следующий шаг."],
            ["Продажи", "Метрики, заявки, переписка, диагностики, возражения и дожим без давления."],
          ].map(([title, text]) => (
            <article className="chalk-card feature-card" key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="board-section" id="program">
        <ChalkTitle eyebrow="программа" title="7 модулей основной программы" />
        <div className="program-list">
          {mainModuleCatalog.map((module, index) => (
            <details className="chalk-details" key={module.title} open={index < 2}>
              <summary>
                <span>Модуль {index + 1}</span>
                <strong>{module.shortTitle}</strong>
              </summary>
              <p>{module.description}</p>
              <div className="mini-list">
                {module.results.slice(0, 4).map((result) => (
                  <span key={result}>{result}</span>
                ))}
              </div>
            </details>
          ))}
        </div>
      </section>

      <section className="board-section" id="tariffs">
        <ChalkTitle
          eyebrow="тарифы"
          title="4 варианта доступа"
          text="Тарифы управляются как данные платформы; в ученическом кабинете контент открывается по выбранному доступу."
        />
        <div className="tariff-grid">
          {tariffs.map((tariff) => (
            <article className="tariff-card pricing-card" key={tariff.id}>
              <span className="chalk-eyebrow">{tariff.highlight}</span>
              <h3>{tariff.title}</h3>
              <strong className="price">{tariff.priceLabel}</strong>
              <p>{tariff.tagline}</p>
              <span className="access-window">{tariff.accessWindow}</span>
              <ul>
                {tariff.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
              </ul>
              <Link className="chalk-button ghost" to="/login">
                Выбрать доступ
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="board-section">
        <ChalkTitle eyebrow="бонусы за 48 часов" title="Материалы, которые ускоряют внедрение" />
        <div className="bonus-line">
          {[
            "100 хуков",
            "AI-промпты",
            "посадочный Telegram-пост",
            "скрипты возражений",
            "чеклист первых 7 дней",
            "UTM + CAC/CPL/ROAS",
            "platform-safe чеклист",
          ].map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>
    </>
  );
}
