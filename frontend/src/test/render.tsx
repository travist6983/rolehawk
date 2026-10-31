import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import { App } from "@/App";

import { fakeFactory } from "./fakeEventSource";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
}

/** Render the whole app at `route`, with a fake EventSource, and wait for the session. */
export async function renderApp(route = "/") {
  const user = userEvent.setup();
  const client = testQueryClient();
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App eventSourceFactory={fakeFactory} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole("navigation", { name: "Main" });
  return { user, client, ...result };
}
