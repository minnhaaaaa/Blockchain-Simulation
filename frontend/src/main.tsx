import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/500.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/manrope/800.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./styles/index.css";
import App from "./App";
import { ApiProvider } from "./api/ApiContext";
import { Cursor, CursorFollow, CursorProvider } from "./components/ui/cursor";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 2000, refetchOnWindowFocus: true }, mutations: { retry: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><ApiProvider><BrowserRouter><CursorProvider global><App /><Cursor/><CursorFollow/></CursorProvider></BrowserRouter></ApiProvider></QueryClientProvider></React.StrictMode>);
