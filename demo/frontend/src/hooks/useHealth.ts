import { useEffect, useState } from "react";
import { getHealth, getMeta } from "../api";
import type { Health, Scenario } from "../types";

/** Backend readiness (polled fast while warming up / indexing, slowly afterwards) and the scenarios. */
export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [modelLabel, setModelLabel] = useState("DeepSeek-V4.1-Flash");

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const tick = async () => {
      try {
        const h = await getHealth();
        if (!alive) return;
        setHealth(h);
        setOffline(false);
        if (h.ready && !scenariosLoaded) loadMeta();
        timer = window.setTimeout(tick, h.ready ? 15000 : 1500);
      } catch {
        if (!alive) return;
        setOffline(true);
        timer = window.setTimeout(tick, 3000);
      }
    };
    let scenariosLoaded = false;
    const loadMeta = () =>
      getMeta()
        .then(m => {
          scenariosLoaded = true;
          setScenarios(m.scenarios);
          if (m.models[0]) setModelLabel(m.models[0].label);
        })
        .catch(() => {});
    loadMeta();
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  return { health, offline, scenarios, modelLabel };
}
