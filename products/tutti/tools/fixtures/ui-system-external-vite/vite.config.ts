import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { tuttiUISystemDev } from "@tutti-os/ui-system/dev-vite";

export default defineConfig({
  plugins: [react(), tailwindcss(), tuttiUISystemDev()]
});
