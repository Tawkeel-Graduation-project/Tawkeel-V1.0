export type Role = "client" | "lawyer";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  role: Role;
}

export const roleLabel: Record<Role, string> = {
  client: "عميل",
  lawyer: "محامٍ",
};

/** Where each role lands after sign-in. */
export const roleHome: Record<Role, string> = {
  client: "/client",
  lawyer: "/lawyer",
};
