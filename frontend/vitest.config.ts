import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Alias "@" igual ao do tsconfig e JSX automático para os testes de componente (jsdom, por arquivo).
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
});
