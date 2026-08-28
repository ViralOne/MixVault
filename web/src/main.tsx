import { render } from "solid-js/web";
import App from "./App";

import "./styles/base.css";
import "./styles/carousel.css";
import "./styles/detail.css";
import "./styles/cooking.css";
import "./styles/manual-anim.css";
import "./styles/panels.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing from index.html");

// Dev-only scene gallery for eyeballing the hands-on animations.
if (import.meta.env.DEV && location.hash === "#/dev/scenes") {
  const { default: SceneGallery } = await import("./components/cooking/SceneGallery");
  render(() => <SceneGallery />, root);
} else {
  render(() => <App />, root);
}
