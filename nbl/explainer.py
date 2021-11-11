from nbl.dataloader_gumtree import NBLGumtreeDGLStatementDataset
from model import GCN_A_L_T_1

import torch.nn.functional as F
import torch.nn as nn
import torch
import tqdm
import math
import os

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


class NodeWeights(nn.Module):
    def __init__(self, num_nodes, num_node_feats):
        super().__init__()
        self.num_nodes = num_nodes
        self.params = nn.Parameter(
            torch.FloatTensor(self.num_nodes, num_node_feats))
        nn.init.normal_(self.params, nn.init.calculate_gain(
            "relu")*math.sqrt(2.0)/(num_nodes*2))
        self.sigmoid = nn.Sigmoid()

    def forward(self, g):
        g.nodes['ast'].data['weight'] = self.sigmoid(self.params)
        return g

class WrapperModel(nn.Module):
    def __init__(self, model, num_nodes, num_node_feats):
        super().__init__()
        self.nweights = NodeWeights(num_nodes, num_node_feats)
        self.model = model

    def forward_old(self, g):
        self.model.add_default_nweight = True
        self.model.eval()
        return self.model(g).nodes['ast'].data['logits']

    def forward(self, g):
        self.model.add_default_nweight = False
        self.model.eval()

        g = self.nweights(g)

        return self.model(g).nodes['ast'].data['logits']


def entropy_loss(masking):
    return torch.mean(
        -torch.sigmoid(masking) * torch.log(torch.sigmoid(masking)) -
        (1 - torch.sigmoid(masking)) * torch.log(1 - torch.sigmoid(masking)))


def entropy_loss_mask(g, coeff_n=0.2, coeff_e=0.5):
    e_e_loss = 0.0
    n_e_loss = coeff_n * entropy_loss(g.nodes['ast'].data['weight'])
    return n_e_loss + e_e_loss

def consistency_loss(preds, labels):
    loss = F.cross_entropy(preds, labels)
    return loss

def explain(model, dataloader, iters=10):

    lr = 3e-3
    os.makedirs('explain_log', exist_ok=True)

    # bar = tqdm.trange(len(dataloader))
    bar = range(len(dataloader))
    for i in bar:
        print('Graph', i)

        g, mask_stmt = dataloader[i]
        if g is None:
            continue
        g = g.to(device)
        mask_stmt = mask_stmt.to(device)

        wrapper = WrapperModel(model, 
                               g.number_of_nodes(),
                               model.hidden_feats).to(device)
        wrapper.nweights.train()
        opt = torch.optim.Adam(wrapper.nweights.parameters(), lr)

        with torch.no_grad():
            ori_logits = wrapper.forward_old(g)
            _, ori_preds = torch.max(ori_logits[mask_stmt].detach().cpu(), dim=1)

        for j, nidx in enumerate(mask_stmt):
            titers = tqdm.tqdm(range(iters))
            titers.set_description(f'Node {nidx}')
            # titers = range(iters)
            for it in titers:
                preds = wrapper(g)
                preds = preds[mask_stmt].detach().cpu()

                loss = entropy_loss_mask(g) \
                     + consistency_loss(preds, ori_preds.squeeze(-1))
                titers.set_postfix(loss=loss.item())

                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    wrapper.nweights.parameters(), 1.0)
                opt.step()


if __name__ == '__main__':
    dataset = NBLGumtreeDGLStatementDataset()
    meta_graph = dataset.meta_graph

    model = GCN_A_L_T_1(
        128, meta_graph,
        device=device,
        num_ast_labels=len(dataset.nx_dataset.ast_types),
        num_classes_ast=2)

    model.load_state_dict(torch.load('model_last.pth', map_location=device))
    explain(model, dataset, iters=1000)
