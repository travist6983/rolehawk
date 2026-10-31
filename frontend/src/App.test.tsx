import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { App } from "@/App";

test("renders the pipeline home screen", () => {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  expect(screen.getByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
});
