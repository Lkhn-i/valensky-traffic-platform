from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.curriculum.services import STAGE3_PREVIEW_COURSE, ensure_stage3_preview_course


class Command(BaseCommand):
    help = "Create or update the published Stage 3 preview course tree."

    def handle(self, *args: object, **options: object) -> None:
        course = ensure_stage3_preview_course()
        module_count = len(STAGE3_PREVIEW_COURSE.modules)
        lesson_count = sum(len(module.lessons) for module in STAGE3_PREVIEW_COURSE.modules)
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Ensured Stage 3 preview course '{course.slug}' with "
                    f"{module_count} modules and {lesson_count} lessons."
                )
            )
        )
