import { createContext, useContext, useEffect, useRef, useState } from "react";
import {
  archiveEntityRequest,
  fetchBootstrap,
  fetchServerState,
  loginRequest,
  logoutRequest,
  resetServerState,
  reviewHomeworkRequest,
  saveEntityRequest,
  saveProgressRequest,
  submitHomeworkRequest,
  uploadCoverImageRequest,
  uploadHomeworkFilesRequest,
  type EntityKey,
  type EntityValue,
} from "../domain/api";
import { getUserById } from "../domain/helpers";
import type {
  AppState,
  HomeworkAnswer,
  HomeworkAttachment,
  LessonProgress,
  LoginResult,
  Session,
  User,
} from "../domain/types";

interface AppContextValue {
  state: AppState;
  session: Session;
  currentUser?: User;
  login: (email: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  resetState: () => void;
  saveEntity: <K extends EntityKey>(key: K, item: EntityValue<K>) => void;
  archiveEntity: <K extends EntityKey>(key: K, id: string) => void;
  uploadCoverImage: (file: File) => Promise<string>;
  uploadHomeworkFiles: (files: File[]) => Promise<HomeworkAttachment[]>;
  submitHomework: (lessonId: string, text: string, attachments: HomeworkAttachment[]) => void;
  reviewHomework: (answerId: string, status: HomeworkAnswer["status"], comment: string) => void;
  saveProgress: (lessonId: string, payload: Partial<LessonProgress>) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

const emptyState: AppState = {
  tariffs: [],
  users: [],
  trainings: [],
  folders: [],
  modules: [],
  lessons: [],
  lessonBlocks: [],
  materials: [],
  homeworkTemplates: [],
  homeworkAnswers: [],
  progress: [],
};

function replaceEntity<K extends EntityKey>(state: AppState, key: K, item: EntityValue<K>): AppState {
  const collection = state[key] as EntityValue<K>[];
  const exists = collection.some((entry) => entry.id === item.id);
  const nextCollection = exists
    ? collection.map((entry) => (entry.id === item.id ? item : entry))
    : [...collection, item];
  return {
    ...state,
    [key]: nextCollection,
  };
}

function archiveEntityLocal<K extends EntityKey>(state: AppState, key: K, id: string): AppState {
  const collection = state[key] as EntityValue<K>[];
  return {
    ...state,
    [key]: collection.map((entry) =>
      entry.id === id && "status" in entry
        ? ({
            ...entry,
            status: "archived",
          } as EntityValue<K>)
        : entry,
    ),
  };
}

function logApiError(error: unknown) {
  console.error(error instanceof Error ? error.message : error);
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AppState>(emptyState);
  const [session, setSession] = useState<Session>({ userId: null });
  const latestStateSequenceRef = useRef(0);

  const applyLatestState = <T,>(promise: Promise<T>, applyResult: (result: T) => void) => {
    latestStateSequenceRef.current += 1;
    const sequence = latestStateSequenceRef.current;

    return promise.then((result) => {
      if (sequence === latestStateSequenceRef.current) {
        applyResult(result);
      }
      return result;
    });
  };

  useEffect(() => {
    let isMounted = true;
    void applyLatestState(fetchBootstrap(), ({ state: nextState, session: nextSession }) => {
      if (!isMounted) {
        return;
      }
      setState(nextState);
      setSession(nextSession);
    })
      .catch(logApiError);

    return () => {
      isMounted = false;
    };
  }, []);

  const currentUser = getUserById(state, session.userId) ?? undefined;

  const login = async (email: string, password: string): Promise<LoginResult> => {
    try {
      const result = await loginRequest(email, password);
      if (!result.ok) {
        return result;
      }
      setSession(result.session ?? { userId: null });
      await applyLatestState(fetchServerState(), setState);
      return result;
    } catch {
      return {
        ok: false,
        message: "API недоступен. Запустите проект через npm run dev.",
      };
    }
  };

  const logout = async () => {
    latestStateSequenceRef.current += 1;
    setSession({ userId: null });
    setState(emptyState);
    try {
      await logoutRequest();
      await applyLatestState(fetchBootstrap(), ({ state: nextState, session: nextSession }) => {
        setState(nextState);
        setSession(nextSession);
      });
    } catch (error) {
      logApiError(error);
    }
  };

  const resetState = () => {
    void applyLatestState(resetServerState(), ({ state: nextState, session: nextSession }) => {
      setState(nextState);
      setSession(nextSession);
    })
      .catch(logApiError);
  };

  const saveEntity = <K extends EntityKey>(key: K, item: EntityValue<K>) => {
    setState((current) => replaceEntity(current, key, item));
    void applyLatestState(saveEntityRequest(key, item), setState).catch(logApiError);
  };

  const archiveEntity = <K extends EntityKey>(key: K, id: string) => {
    setState((current) => archiveEntityLocal(current, key, id));
    void applyLatestState(archiveEntityRequest(key, id), setState).catch(logApiError);
  };

  const submitHomework = (lessonId: string, text: string, attachments: HomeworkAttachment[]) => {
    void applyLatestState(submitHomeworkRequest(lessonId, text, attachments), setState).catch(logApiError);
  };

  const reviewHomework = (answerId: string, status: HomeworkAnswer["status"], comment: string) => {
    void applyLatestState(reviewHomeworkRequest(answerId, status, comment), setState).catch(logApiError);
  };

  const saveProgress = (lessonId: string, payload: Partial<LessonProgress>) => {
    void applyLatestState(saveProgressRequest(lessonId, payload), setState).catch(logApiError);
  };

  return (
    <AppContext.Provider
      value={{
        state,
        session,
        currentUser,
        login,
        logout,
        resetState,
        saveEntity,
        archiveEntity,
        uploadCoverImage: uploadCoverImageRequest,
        uploadHomeworkFiles: uploadHomeworkFilesRequest,
        submitHomework,
        reviewHomework,
        saveProgress,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used inside AppProvider");
  }
  return context;
}
