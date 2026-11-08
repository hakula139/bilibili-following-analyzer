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
      url = "github:hakula139/devkit/v1";
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
        dk = devkit.lib.mkLib pkgs;

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
        preCommit = dk.preCommit {
          src = ./.;
          hooks = {
            actionlint.enable = true;
            check-yaml.enable = true;
            cspell.enable = true;
            deadnix.enable = true;
            dprint.enable = true;
            markdownlint-cli2.enable = true;
            nixfmt.enable = true;
            prettier.enable = true;
            shellcheck.enable = true;
            shfmt.enable = true;
            sort-file-contents.enable = true;
            statix.enable = true;
            taplo.enable = true;
          };

          devHooks = {
            mypy = {
              enable = true;
              package = null;
              entry = "${pkgs.lib.getExe (dk.uvTool "mypy")}";
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
              package = null;
              entry = "${pkgs.lib.getExe (dk.uvTool "ruff")} check --fix";
              language = "system";
              types = [ "file" ];
              types_or = [
                "python"
                "pyi"
              ];
            };
            ruff-format = {
              enable = true;
              package = null;
              entry = "${pkgs.lib.getExe (dk.uvTool "ruff")} format";
              language = "system";
              types = [ "file" ];
              types_or = [
                "python"
                "pyi"
              ];
            };
            bandit = {
              enable = true;
              package = null;
              entry = "${pkgs.lib.getExe (dk.uvTool "bandit")} -r bilibili_following_analyzer/";
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
