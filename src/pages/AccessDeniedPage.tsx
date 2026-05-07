import { useSearchParams } from "react-router-dom";
import { AccessDeniedPanel } from "../components/ui";
import type { AccessReason } from "../domain/types";

const reasonText: Record<AccessReason, string> = {
  ok: "Доступ открыт",
  login: "Нужно войти",
  tariff: "Недоступно на вашем тарифе",
  expired: "Доступ истек",
  unpublished: "Материал еще не опубликован",
  previous: "Нужно завершить предыдущий урок",
};

export function AccessDeniedPage() {
  const [params] = useSearchParams();
  const reason = (params.get("reason") || "tariff") as AccessReason;
  const title = params.get("title") || "Материал закрыт";

  return (
    <AccessDeniedPanel
      title={title}
      result={{
        allowed: false,
        reason,
        message: reasonText[reason] || reasonText.tariff,
      }}
      backTo="/trainings"
    />
  );
}
