import torch
from torch.optim import Optimizer

class SAM(Optimizer):
    """
    Sharpness-Aware Minimization (SAM) Wrapper.
    
    Ref: Foret et al. 2020 (https://arxiv.org/abs/2010.01495)
    
    SAM seeks parameters in neighborhoods of uniformly low loss by pertubing weights
    prior to performing the actual optimization step.
    """
    def __init__(self, params, base_optimizer_cls, rho: float = 0.05, **kwargs):
        assert rho >= 0.0, f"Invalid rho, should be non-negative: {rho}"
        defaults = dict(rho=rho, **kwargs)
        super(SAM, self).__init__(params, defaults)
        
        self.base_optimizer = base_optimizer_cls(self.param_groups, **kwargs)
        self.param_groups = self.base_optimizer.param_groups

    @torch.no_grad()
    def first_step(self, zero_grad: bool = False):
        """Computes the adversarial perturbation and perturbs the weights."""
        grad_norm = self._grad_norm()
        for group in self.param_groups:
            scale = group["rho"] / (grad_norm + 1e-12)
            for p in group["params"]:
                if p.grad is None:
                    continue
                # Save original parameter states to restore later
                self.state[p]["old_p"] = p.data.clone()
                e_w = p.grad.data * scale.to(p)
                p.add_(e_w)  # w_t + e(w)

        if zero_grad:
            self.zero_grad()

    @torch.no_grad()
    def second_step(self, zero_grad: bool = False):
        """Restores original weights and performs base optimizer step."""
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                # Restore original parameter values
                if "old_p" in self.state[p]:
                    p.data = self.state[p]["old_p"]
                    
        # Perform standard optimizer update on original weights using the perturbed gradients
        self.base_optimizer.step()

        if zero_grad:
            self.zero_grad()

    def _grad_norm(self):
        shared_device = self.param_groups[0]["params"][0].device
        norm = torch.norm(
            torch.stack([
                p.grad.norm(p=2).to(shared_device)
                for group in self.param_groups for p in group["params"]
                if p.grad is not None
            ]),
            p=2
        )
        return norm

    def step(self, closure=None):
        raise NotImplementedError("SAM requires a two-step forward/backward pass. Use first_step() and second_step().")
