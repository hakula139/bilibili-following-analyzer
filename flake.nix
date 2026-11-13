# ==============================================================================
# Bilibili Following Analyzer Development Flake
# ==============================================================================

{
  description = "Bilibili following analyzer development environment";

  # ----------------------------------------------------------------------------
  # Inputs
  # ----------------------------------------------------------------------------
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    devkit = {
      url = "github:hakula139/devkit/v3";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # ----------------------------------------------------------------------------
  # Outputs
  # ----------------------------------------------------------------------------
  outputs =
    {
      nixpkgs,
      devkit,
      ...
    }:
    devkit.lib.eachSystem devkit.lib.systems (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        dk = devkit.lib.mkLib pkgs;

        # ----------------------------------------------------------------------
        # Pre-commit hooks
        # ----------------------------------------------------------------------
        preCommit = dk.preCommit {
          src = ./.;
          hooks = {
            mypy.enable = true;
            prettier.enable = true;
            ruff.enable = true;
            ruff-format.enable = true;
            shellcheck.enable = true;
            shfmt.enable = true;
            taplo.enable = true;
          };
        };
      in
      {
        devShells.default = pkgs.mkShell {
          name = "bilibili-following-analyzer-dev";
          packages = [ pkgs.python313 ] ++ builtins.attrValues dk.uvToolchain;
          inputsFrom = [ preCommit ];
        };

        formatter = pkgs.nixfmt-tree;
      }
    );
}
