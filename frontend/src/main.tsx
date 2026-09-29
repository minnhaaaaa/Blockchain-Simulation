import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "./styles/index.css";
import App from "./App";
import { ApiProvider } from "./api/ApiContext";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 2000, refetchOnWindowFocus: true }, mutations: { retry: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><ApiProvider><BrowserRouter><App /></BrowserRouter></ApiProvider></QueryClientProvider></React.StrictMode>);
