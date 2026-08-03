// Shared mutable state — import { state } and mutate state.xxx = value
export const state = {
  serverPort:        null,
  currentResult:     null,
  currentXmlPath:    null,
  currentCachedPath: null,
  currentSnapshotId: null,
  currentModules:    null,   // {modules, module_order}
  currentModule:     null,   // selected module key ('dangling' | 'float')
};
