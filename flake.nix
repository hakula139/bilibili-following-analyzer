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
    git-hooks-nix = {
      url = "github:cachix/git-hooks.nix";
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
      git-hooks-nix,
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
        repositoryHooks = {
          actionlint.enable = true;
          check-added-large-files.enable = true;
          check-yaml.enable = true;
          cspell = {
            enable = true;
            args = [
              "--no-progress"
              "--no-must-find-files"
            ];
          };
          deadnix.enable = true;
          end-of-file-fixer.enable = true;
          markdownlint-cli2 = {
            enable = true;
            entry = "${pkgs.markdownlint-cli2}/bin/markdownlint-cli2";
            files = "\\.md$";
          };
          nixfmt.enable = true;
          statix.enable = true;
          trim-trailing-whitespace = {
            enable = true;
            args = [ "--markdown-linebreak-ext=md" ];
          };
        };

        preCommitCheck = git-hooks-nix.lib.${system}.run {
          src = ./.;
          package = pkgs.prek;
          hooks = repositoryHooks;
        };

        preCommitHooks = git-hooks-nix.lib.${system}.run {
          src = ./.;
          package = pkgs.prek;
          hooks = repositoryHooks // {
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
        checks.pre-commit = preCommitCheck;

        devShells.python = pkgs.mkShell pythonEnvironment;

        devShells.default = pkgs.mkShell (
          pythonEnvironment
          // {
            packages = pythonEnvironment.packages ++ preCommitHooks.enabledPackages;
            inherit (preCommitHooks) shellHook;
          }
        );

        formatter = pkgs.nixfmt-tree;
      }
    );
}
