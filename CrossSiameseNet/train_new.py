import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.optim import Adam
import logging
from datetime import datetime
import pandas as pd
from CrossSiameseNet.checkpoints import save_checkpoint
from CrossSiameseNet.BatchShaper import BatchShaper
from CrossSiameseNet.loss import WeightedTripletMarginLoss
import numpy as np

def train_triplet(model, dataset_name: str, train_loader: DataLoader, test_loader: DataLoader, 
                  n_epochs: int, device, checkpoints_dir: str, use_fixed_training_triplets: bool = False,
                  training_type: str = None, alpha: float = None, weight_scenario = None):
    
    model = model.to(device)
    optimizer = Adam(model.parameters(), lr=1e-5)    

    weights_1 = len(train_loader.dataset.indices_0) / len(train_loader.dataset.indices_1)

    criterion_triplet_loss = WeightedTripletMarginLoss(device, train_loader.batch_size, weights_1)
    batch_shaper = BatchShaper(device, training_type, alpha)

    train_loss = []
    test_loss = []

    for epoch in range(0, n_epochs):
        
        checkpoint = {}

        # set fixed training dataset for models comparison
        if epoch > 0 and use_fixed_training_triplets:
                train_loader.dataset.refresh_fixed_triplets(train_loader.dataset.seed_fixed_triplets + epoch)

        for state, loader in zip(["train", "test"], [train_loader, test_loader]):
            
            # calculated parameters
            running_loss = 0.0

            if state == "train":
                model.train()
                loader.dataset.shuffle_data(train_loader.batch_size)

            else:
                model.eval()

            for batch_id, (anchor_mf, positive_mf, negative_mf, anchor_label) in enumerate(loader):

                with torch.set_grad_enabled(state == 'train'):
                    
                    optimizer.zero_grad()

                    anchor_mf, positive_mf, negative_mf, anchor_label = batch_shaper.shape_batch(anchor_mf, positive_mf, negative_mf, anchor_label, model, state)

                    loss = criterion_triplet_loss(anchor_mf, positive_mf, negative_mf, anchor_label)

                    if state == "train":
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item()

            epoch_loss = round(running_loss / (batch_id + 1), 5)


            logging.info(f"Epoch: {epoch}, state: {state}, loss: {epoch_loss}")

            # update report
            if state == "train":
                train_loss.append(epoch_loss)
            else:
                test_loss.append(epoch_loss)

        # save model to checkpoint
        checkpoint["epoch"] = epoch
        checkpoint["model_state_dict"] = model.state_dict()
        checkpoint["dataset"] = dataset_name
        checkpoint['train_loss'] = train_loss
        checkpoint['test_loss'] = test_loss
        checkpoint['used_fixed_training_triplets'] = use_fixed_training_triplets
        checkpoint["save_dttm"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        checkpoint_path = f"{checkpoints_dir}/{dataset_name}_{epoch}"
        save_checkpoint(checkpoint, checkpoint_path)
    
    # save report
    report_df = pd.DataFrame({
        "epoch": [n_epoch for n_epoch in range(0, n_epochs)], 
        "train_loss": train_loss, 
        "test_loss": test_loss})
    report_df.to_excel(f"{checkpoints_dir}/train_report_{dataset_name}.xlsx", index=False)