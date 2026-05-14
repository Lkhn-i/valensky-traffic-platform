import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChalkTitle } from "../components/ui";
import { fetchRobokassaPaymentStatus, type RobokassaPaymentStatusPayload } from "../domain/api";

export function PaymentStatusPage() {
  const location = useLocation();
  const isSuccess = location.pathname.endsWith("/success");
  const [status, setStatus] = useState<RobokassaPaymentStatusPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(isSuccess);
  const [copiedField, setCopiedField] = useState<"login" | "password" | "">("");

  useEffect(() => {
    if (!isSuccess) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    fetchRobokassaPaymentStatus(location.search)
      .then((payload) => {
        if (active) {
          setStatus(payload);
          setError("");
        }
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : "Не удалось проверить платеж.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [isSuccess, location.search]);

  const copyCredential = (field: "login" | "password", value: string) => {
    if (!value || !navigator.clipboard) {
      return;
    }
    void navigator.clipboard.writeText(value).then(() => {
      setCopiedField(field);
      window.setTimeout(() => setCopiedField(""), 1600);
    });
  };

  const cabinetUrl = status?.access?.loginUrl ? new URL(status.access.loginUrl).pathname : "/trainings";

  return (
    <section className="board-section payment-status-page">
      <ChalkTitle
        eyebrow="оплата"
        title={isSuccess ? "Платеж принят" : "Платеж не завершен"}
        text={
          isSuccess
            ? "Проверяем платеж и готовим данные для входа в личный кабинет."
            : "Оплата не прошла или была отменена. Можно вернуться к тарифам и попробовать еще раз."
        }
      />
      <div className="chalk-panel payment-result-panel">
        {loading ? <p className="checkout-success">Проверяем подтверждение оплаты...</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {status?.access ? (
          <div className="payment-result-layout">
            <div className="access-credentials">
              <span className="chalk-eyebrow">данные доступа</span>
              <h2>{status.order.tariffTitle}</h2>
              {status.delivery?.status === "sent" ? (
                <p>
                  Доступ открыт. Мы отправили логин и пароль на {status.order.customerEmail}. На этом устройстве вход
                  уже выполнен, можно сразу перейти в кабинет.
                </p>
              ) : status.delivery?.status === "outbox" ? (
                <p>
                  Доступ открыт. На этом устройстве вход уже выполнен; письмо будет отправлено повторно автоматически.
                </p>
              ) : (
                <p>Доступ открыт. На этом устройстве вход уже выполнен, сохрани данные ниже на всякий случай.</p>
              )}
              <dl className="credential-list">
                <div className="credential-row">
                  <dt>Логин</dt>
                  <dd>
                    <code>{status.access.login}</code>
                    <button
                      className="copy-button"
                      type="button"
                      onClick={() => copyCredential("login", status.access?.login || "")}
                    >
                      {copiedField === "login" ? "Скопировано" : "Копировать"}
                    </button>
                  </dd>
                </div>
                {status.access.password ? (
                  <div className="credential-row">
                    <dt>Пароль</dt>
                    <dd>
                      <code>{status.access.password}</code>
                      <button
                        className="copy-button"
                        type="button"
                        onClick={() => copyCredential("password", status.access?.password || "")}
                      >
                        {copiedField === "password" ? "Скопировано" : "Копировать"}
                      </button>
                    </dd>
                  </div>
                ) : (
                  <div className="credential-row">
                    <dt>Пароль</dt>
                    <dd>
                      <span>Отправлен на почту. Если письмо потерялось, поддержка восстановит доступ по email оплаты.</span>
                    </dd>
                  </div>
                )}
              </dl>
            </div>
            <aside className="payment-next-steps">
              <strong>Что дальше</strong>
              <p>Нажми «Перейти в кабинет» — браузер уже получил безопасную сессию после оплаты.</p>
              <p>Данные доступа также отправляются на почту. Если письма нет во входящих, проверь «Спам».</p>
            </aside>
          </div>
        ) : null}
        <div className="action-row payment-actions">
          <Link className="chalk-button" to="/#tariffs">
            Вернуться к тарифам
          </Link>
          {status?.access ? (
            <a className="chalk-button ghost" href={cabinetUrl}>
              Перейти в кабинет
            </a>
          ) : (
            <Link className="chalk-button ghost" to="/login">
              Войти в кабинет
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
