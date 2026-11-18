import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "wxt";

/** Compiles rem to px so the host page's html font-size cannot rescale the shadow-root UI. */
function remToPx() {
  return {
    postcssPlugin: "aporia-rem-to-px",
    Declaration(decl: { value: string }) {
      if (decl.value.includes("rem")) {
        decl.value = decl.value.replace(
          /(-?\d*\.?\d+)rem\b/g,
          (_m, n: string) => `${parseFloat(n) * 16}px`,
        );
      }
    },
  };
}

// See https://wxt.dev/api/reference/wxt/interfaces/inlineconfig.html
export default defineConfig({
  srcDir: "src",
  modules: ["@wxt-dev/module-react"],
  vite: () => ({
    plugins: [tailwindcss()],
    css: { postcss: { plugins: [remToPx()] } },
  }),
  manifest: ({ mode }) => ({
    name: "Aporia",
    permissions: ["storage"],
    // The local API is only reachable from development builds.
    host_permissions: [
      "https://leetcode.com/*",
      ...(mode === "development" ? ["http://localhost:8000/*"] : []),
    ],
  }),
});
