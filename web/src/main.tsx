import "@fontsource/neuton/400.css";
import "@fontsource/neuton/700.css";
import "@fontsource/poppins/400.css";
import "@fontsource/poppins/500.css";
import "@fontsource/poppins/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "./styles/index.css";

import { keepPreviousData, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";

// Keep the previous data on screen while a new query loads (no flash of skeletons when switching tabs or filters).
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, gcTime: 10 * 60_000, refetchOnWindowFocus: false, retry: 1, placeholderData: keepPreviousData } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
