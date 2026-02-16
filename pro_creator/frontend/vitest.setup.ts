// Some environments run with NODE_ENV=production; force test mode so React uses dev builds.
process.env.NODE_ENV = "test";
// Inform React that we're in a test environment (avoids act-related warnings in newer React).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

import "@testing-library/jest-dom";
