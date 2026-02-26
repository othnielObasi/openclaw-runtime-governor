declare module "../components/GovernorComplete" {
  import type React from "react";
  const GovernorApp: React.ComponentType<any>;
  export default GovernorApp;
}

declare module "../components/*" {
  import type React from "react";
  const Component: React.ComponentType<any>;
  export default Component;
}

declare module "*.jsx" {
  import type React from "react";
  const Component: React.ComponentType<any>;
  export default Component;
}
