import { Link } from "react-router-dom";

import { EmptyState } from "@/components/States";

export default function NotFound() {
  return <EmptyState title="Page not found" action={<Link to="/" className="text-brand">Go home</Link>} />;
}
