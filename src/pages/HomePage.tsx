import { FormEvent, useState } from "react";
import { useApp } from "../app/context";
import { ChalkTitle, LegalConsent, MarketingConsent } from "../components/ui";
import { createRobokassaCheckoutRequest } from "../domain/api";
import { mainModuleCatalog } from "../domain/catalog";
import type { Tariff } from "../domain/types";

const initialCheckoutForm = {
  name: "",
  email: "",
  phone: "",
};

export function HomePage() {
  const { state } = useApp();
  const [selectedTariff, setSelectedTariff] = useState<Tariff | null>(null);
  const [checkoutForm, setCheckoutForm] = useState(initialCheckoutForm);
  const [checkoutConsent, setCheckoutConsent] = useState(false);
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [checkoutSubmitting, setCheckoutSubmitting] = useState(false);
  const tariffs = state.tariffs
    .filter((tariff) => tariff.id !== "zero")
    .sort((left, right) => left.sortOrder - right.sortOrder);

  const closeCheckout = () => {
    setSelectedTariff(null);
    setCheckoutForm(initialCheckoutForm);
    setCheckoutConsent(false);
    setMarketingConsent(false);
    setCheckoutError("");
    setCheckoutSubmitting(false);
  };

  const openCheckout = (tariff: Tariff) => {
    setSelectedTariff(tariff);
    setCheckoutForm(initialCheckoutForm);
    setCheckoutConsent(false);
    setMarketingConsent(false);
    setCheckoutError("");
    setCheckoutSubmitting(false);
  };

  const submitPaymentForm = (action: string, fields: Record<string, string>) => {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = action;
    form.style.display = "none";

    Object.entries(fields).forEach(([name, value]) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = String(value);
      form.appendChild(input);
    });

    document.body.appendChild(form);
    form.submit();
  };

  const handleCheckoutSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedTariff) {
      return;
    }
    if (checkoutSubmitting) {
      return;
    }
    if (!checkoutForm.name.trim() || !checkoutForm.email.trim() || !checkoutForm.phone.trim()) {
      setCheckoutError("Заполни имя, email и телефон, чтобы мы могли выдать доступ после оплаты.");
      return;
    }
    if (!checkoutConsent) {
      setCheckoutError("Перед переходом к оплате нужно принять документы и согласие на обработку данных.");
      return;
    }

    try {
      setCheckoutSubmitting(true);
      setCheckoutError("");
      const checkout = await createRobokassaCheckoutRequest({
        tariffId: selectedTariff.id,
        ...checkoutForm,
        acceptedLegal: true,
        acceptedMarketing: marketingConsent,
      });
      submitPaymentForm(checkout.payment.action, checkout.payment.fields);
    } catch (error) {
      setCheckoutError(error instanceof Error ? error.message : "Не удалось перейти к оплате.");
      setCheckoutSubmitting(false);
    }
  };

  return (
    <>
      <section className="hero-cover" aria-label="Место для главной обложки">
        <img
          className="hero-cover-image"
          src="/media/valensky-traffic-cover.png"
          alt="Валенский. Курс по трафику, который приносит результат"
        />
      </section>

      <section className="board-section">
        <ChalkTitle
          eyebrow="что собираем"
          title="Рабочая система роста"
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
              <button className="chalk-button ghost" type="button" onClick={() => openCheckout(tariff)}>
                Выбрать доступ
              </button>
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

      {selectedTariff ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={closeCheckout}>
          <section
            className="chalk-panel checkout-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="checkout-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="modal-close" type="button" aria-label="Закрыть окно" onClick={closeCheckout}>
              x
            </button>
            <span className="chalk-eyebrow">оформление доступа</span>
            <h2 id="checkout-title">{selectedTariff.title}</h2>
            <p>
              Оставь данные для выдачи доступа. Они нужны, чтобы после оплаты открыть кабинет и отправить входные данные.
            </p>
            <div className="checkout-summary">
              <strong>{selectedTariff.priceLabel}</strong>
              <span>{selectedTariff.accessWindow}</span>
            </div>
            <form className="checkout-form" onSubmit={handleCheckoutSubmit}>
              <label>
                Имя и фамилия
                <input
                  value={checkoutForm.name}
                  required
                  onChange={(event) => {
                    setCheckoutForm((current) => ({ ...current, name: event.target.value }));
                    setCheckoutError("");
                  }}
                  autoComplete="name"
                />
              </label>
              <label>
                Email для доступа
                <input
                  type="email"
                  value={checkoutForm.email}
                  required
                  onChange={(event) => {
                    setCheckoutForm((current) => ({ ...current, email: event.target.value }));
                    setCheckoutError("");
                  }}
                  autoComplete="email"
                />
              </label>
              <label>
                Телефон
                <input
                  value={checkoutForm.phone}
                  required
                  inputMode="tel"
                  onChange={(event) => {
                    setCheckoutForm((current) => ({ ...current, phone: event.target.value }));
                    setCheckoutError("");
                  }}
                  autoComplete="tel"
                />
              </label>
              <LegalConsent
                id={`checkout-legal-consent-${selectedTariff.id}`}
                checked={checkoutConsent}
                context="payment"
                onChange={(checked) => {
                  setCheckoutConsent(checked);
                  setCheckoutError("");
                }}
              />
              <MarketingConsent
                id={`checkout-marketing-consent-${selectedTariff.id}`}
                checked={marketingConsent}
                onChange={setMarketingConsent}
              />
              {checkoutError ? <p className="form-error">{checkoutError}</p> : null}
              {checkoutSubmitting ? (
                <p className="checkout-success">
                  Создаем безопасный платеж и переходим в Robokassa...
                </p>
              ) : null}
              <div className="action-row checkout-actions">
                <button className="chalk-button" type="submit" disabled={checkoutSubmitting}>
                  {checkoutSubmitting ? "Переходим..." : "Перейти к оплате"}
                </button>
                <button className="chalk-button ghost" type="button" onClick={closeCheckout} disabled={checkoutSubmitting}>
                  Отмена
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </>
  );
}
