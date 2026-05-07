import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../components/AppLayout";
import { AccessDeniedPage } from "../pages/AccessDeniedPage";
import { AdminPage } from "../pages/AdminPage";
import { FolderPage } from "../pages/FolderPage";
import { HomePage } from "../pages/HomePage";
import { LessonPage } from "../pages/LessonPage";
import { LoginPage } from "../pages/LoginPage";
import { ManagerHomeworksPage } from "../pages/ManagerHomeworksPage";
import { ModulePage } from "../pages/ModulePage";
import { StudentCardPage } from "../pages/StudentCardPage";
import { TrainingPage } from "../pages/TrainingPage";
import { TrainingsPage } from "../pages/TrainingsPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/trainings" element={<TrainingsPage />} />
        <Route path="/trainings/:trainingId" element={<TrainingPage />} />
        <Route path="/trainings/:trainingId/folders/:folderId" element={<FolderPage />} />
        <Route path="/trainings/:trainingId/modules/:moduleId" element={<ModulePage />} />
        <Route
          path="/trainings/:trainingId/modules/:moduleId/lessons/:lessonId"
          element={<LessonPage />}
        />
        <Route path="/access-denied" element={<AccessDeniedPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/manager/homeworks" element={<ManagerHomeworksPage />} />
        <Route path="/manager/students/:studentId" element={<StudentCardPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
