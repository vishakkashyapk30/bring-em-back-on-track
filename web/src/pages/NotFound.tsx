import { Link } from "react-router-dom";

import { EmptyState } from "@/components/States";

export default function NotFound() {
  return <EmptyState title="We can't find that page" action={<Link to="/" className="text-brand">Back to the home page</Link>} />;
}
