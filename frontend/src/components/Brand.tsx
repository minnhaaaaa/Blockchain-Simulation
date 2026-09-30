import { Link } from "react-router-dom";
import { HyperText } from "./ui/text-motion";
export function Brand() {
  return <Link to="/" className="brand" aria-label="Certa home"><HyperText>Certa</HyperText></Link>;
}
