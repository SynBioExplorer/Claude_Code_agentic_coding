"""Interface contract generation and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_orchestrator.schemas.tasks import ContractSpec
from claude_orchestrator.utils.git import get_short_commit


@dataclass
class ContractRenegotiation:
    """Record of a contract renegotiation."""

    contract_name: str
    old_version: str
    new_version: str
    reason: str
    timestamp: str


@dataclass
class ContractManager:
    """Manages interface contracts for cross-task dependencies."""

    contracts_dir: Path = field(default_factory=lambda: Path("contracts"))
    max_renegotiations: int = 2

    # Track renegotiations per contract
    _renegotiations: dict[str, list[ContractRenegotiation]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    def generate_contract(
        self,
        name: str,
        methods: list[dict[str, Any]],
        description: str = "",
    ) -> ContractSpec:
        """Generate a new interface contract.

        Args:
            name: Contract name (e.g., AuthServiceProtocol)
            methods: List of method definitions
            description: Contract description

        Returns:
            ContractSpec for the generated contract
        """
        # Get version from current commit
        version = get_short_commit() or "unknown"
        timestamp = datetime.now().isoformat()

        # Generate contract file content
        content = self._generate_contract_content(name, methods, version, timestamp, description)

        # Write contract file
        file_path = self.contracts_dir / f"{self._to_snake_case(name)}.py"
        file_path.write_text(content)

        # Extract method names
        method_names = [m.get("name", "") for m in methods]

        return ContractSpec(
            name=name,
            version=version,
            file_path=str(file_path),
            methods=method_names,
            created_at=timestamp,
            consumers=[],
        )

    def _generate_contract_content(
        self,
        name: str,
        methods: list[dict[str, Any]],
        version: str,
        timestamp: str,
        description: str,
    ) -> str:
        """Generate Python contract file content.

        Args:
            name: Contract name
            methods: Method definitions
            version: Version hash
            timestamp: Creation timestamp
            description: Contract description

        Returns:
            Python source code for the contract
        """
        lines = [
            '"""',
            f"Contract: {name}",
            f"Version: {version} (commit hash when contract was created)",
            f"Generated: {timestamp}",
        ]

        if description:
            lines.append("")
            lines.append(description)

        lines.extend([
            '"""',
            "",
            "from typing import Protocol, Any",
            "",
            "",
            f"class {name}(Protocol):",
        ])

        if not methods:
            lines.append("    pass")
        else:
            for method in methods:
                method_name = method.get("name", "method")
                params = method.get("params", [])
                return_type = method.get("return_type", "Any")
                docstring = method.get("docstring", "")

                # Build parameter string
                param_parts = ["self"]
                for param in params:
                    param_name = param.get("name", "param")
                    param_type = param.get("type", "Any")
                    param_parts.append(f"{param_name}: {param_type}")
                param_str = ", ".join(param_parts)

                lines.append(f"    def {method_name}({param_str}) -> {return_type}:")
                if docstring:
                    lines.append(f'        """{docstring}"""')
                lines.append("        ...")
                lines.append("")

        return "\n".join(lines)

    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase to snake_case.

        Args:
            name: CamelCase name

        Returns:
            snake_case name
        """
        import re

        # Insert underscores before uppercase letters
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def load_contract(self, name: str) -> ContractSpec | None:
        """Load a contract from the contracts directory.

        Args:
            name: Contract name

        Returns:
            ContractSpec if found, None otherwise
        """
        # Try both naming conventions
        candidates = [
            self.contracts_dir / f"{name}.py",
            self.contracts_dir / f"{self._to_snake_case(name)}.py",
        ]

        for file_path in candidates:
            if file_path.exists():
                content = file_path.read_text()
                return self._parse_contract_file(file_path, content)

        return None

    def _parse_contract_file(self, file_path: Path, content: str) -> ContractSpec | None:
        """Parse a contract file to extract metadata.

        Args:
            file_path: Path to contract file
            content: File content

        Returns:
            ContractSpec if parseable, None otherwise
        """
        import re

        # Extract metadata from docstring
        name_match = re.search(r"Contract: (\w+)", content)
        version_match = re.search(r"Version: (\w+)", content)
        generated_match = re.search(r"Generated: ([\d\-T:]+)", content)

        if not name_match or not version_match:
            return None

        name = name_match.group(1)
        version = version_match.group(1)
        created_at = generated_match.group(1) if generated_match else ""

        # Extract method names
        method_matches = re.findall(r"def (\w+)\(self", content)
        methods = [m for m in method_matches if m != "__init__"]

        return ContractSpec(
            name=name,
            version=version,
            file_path=str(file_path),
            methods=methods,
            created_at=created_at,
            consumers=[],
        )

    def version_contract(self, name: str) -> str | None:
        """Get the version hash for a contract.

        Args:
            name: Contract name

        Returns:
            Version hash, or None if contract not found
        """
        contract = self.load_contract(name)
        return contract.version if contract else None

    def verify_contract_compatibility(
        self,
        name: str,
        expected_version: str,
    ) -> tuple[bool, str | None]:
        """Verify a contract matches the expected version.

        Args:
            name: Contract name
            expected_version: Expected version hash

        Returns:
            Tuple of (compatible, error_message)
        """
        contract = self.load_contract(name)

        if not contract:
            return False, f"Contract {name} not found"

        if contract.version != expected_version:
            return False, (
                f"Contract {name} version mismatch: "
                f"expected {expected_version}, found {contract.version}"
            )

        return True, None

    def can_renegotiate(self, name: str) -> bool:
        """Check if a contract can be renegotiated.

        Args:
            name: Contract name

        Returns:
            True if renegotiation count is below max
        """
        renegotiations = self._renegotiations.get(name, [])
        return len(renegotiations) < self.max_renegotiations

    def track_renegotiation(
        self,
        name: str,
        old_version: str,
        new_version: str,
        reason: str,
    ) -> bool:
        """Track a contract renegotiation.

        Args:
            name: Contract name
            old_version: Previous version
            new_version: New version
            reason: Reason for renegotiation

        Returns:
            True if renegotiation was tracked, False if max reached
        """
        if not self.can_renegotiate(name):
            return False

        if name not in self._renegotiations:
            self._renegotiations[name] = []

        self._renegotiations[name].append(
            ContractRenegotiation(
                contract_name=name,
                old_version=old_version,
                new_version=new_version,
                reason=reason,
                timestamp=datetime.now().isoformat(),
            )
        )

        return True

    def get_renegotiation_count(self, name: str) -> int:
        """Get the number of renegotiations for a contract.

        Args:
            name: Contract name

        Returns:
            Number of renegotiations
        """
        return len(self._renegotiations.get(name, []))

    def list_contracts(self) -> list[ContractSpec]:
        """List all contracts in the contracts directory.

        Returns:
            List of ContractSpec for all contracts
        """
        contracts: list[ContractSpec] = []

        if not self.contracts_dir.exists():
            return contracts

        for file_path in self.contracts_dir.glob("*.py"):
            if file_path.name.startswith("__"):
                continue

            content = file_path.read_text()
            contract = self._parse_contract_file(file_path, content)
            if contract:
                contracts.append(contract)

        return contracts


def generate_contract_stub(
    name: str,
    methods: list[dict[str, Any]],
    output_dir: Path | str = "contracts",
) -> str:
    """Generate a contract stub file.

    Convenience function for generating contract stubs.

    Args:
        name: Contract name
        methods: Method definitions
        output_dir: Output directory

    Returns:
        Path to generated contract file
    """
    manager = ContractManager(contracts_dir=Path(output_dir))
    spec = manager.generate_contract(name, methods)
    return spec.file_path
