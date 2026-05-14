import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppProvider } from "./app/context";
import { App } from "./app/App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
