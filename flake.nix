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
    flake-utils.url = "github:numtide/flake-utils";
    devkit = {
      url = "github:hakula139/devkit/v1.0.0-rc.3";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # ----------------------------------------------------------------------------
  # Outputs
  # ----------------------------------------------------------------------------
  outputs =
    {
      nixpkgs,
      flake-utils,
      devkit,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # ----------------------------------------------------------------------
        # Python environment
        # ----------------------------------------------------------------------
        pythonEnvironment = {
          packages = with pkgs; [
            python313
            uv
          ];
          UV_PYTHON_DOWNLOADS = "never";
        };

        # ----------------------------------------------------------------------
        # Pre-commit hooks
        # ----------------------------------------------------------------------
        preCommit = (devkit.lib.mkLib pkgs).preCommit {
          src = ./.;
          devHooks = {
            mypy = {
              enable = true;
              package = pkgs.uv;
              entry = "${pkgs.uv}/bin/uv run --locked mypy";
              language = "system";
              files = "\\.pyi?$";
              types_or = [
                "python"
                "pyi"
              ];
              pass_filenames = false;
            };
            ruff = {
              enable = true;
              package = pkgs.uv;
              entry = "${pkgs.uv}/bin/uv run --locked ruff check --fix";
              language = "system";
              types = [ "file" ];
              types_or = [
                "python"
                "pyi"
              ];
            };
            ruff-format = {
              enable = true;
              package = pkgs.uv;
              entry = "${pkgs.uv}/bin/uv run --locked ruff format";
              language = "system";
              types = [ "file" ];
              types_or = [
                "python"
                "pyi"
              ];
            };
            bandit = {
              enable = true;
              package = pkgs.uv;
              entry = "${pkgs.uv}/bin/uv run --locked bandit -r bilibili_following_analyzer/";
              language = "system";
              files = "^bilibili_following_analyzer/.*\\.py$";
              pass_filenames = false;
            };
          };
        };
      in
      {
        checks.pre-commit = preCommit.check;

        devShells.python = pkgs.mkShell pythonEnvironment;

        devShells.default = pkgs.mkShell (
          pythonEnvironment
          // {
            inputsFrom = [ preCommit.shell ];
          }
        );

        formatter = pkgs.nixfmt-tree;
      }
    );
}
