from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as transforms
from torchvision import models
from huggingface_hub import hf_hub_download
import json

# Architecture correcte du modèle (depuis HuggingFace)
class PlantDiseaseClassifier(nn.Module):
    def __init__(self, num_classes, dropout_rate=0.3):
        super(PlantDiseaseClassifier, self).__init__()
        
        # Use EfficientNet as backbone
        self.backbone = models.efficientnet_b2(pretrained=False)
        
        # Get feature dimension
        num_features = self.backbone.classifier[1].in_features
        
        # Replace classifier with custom head
        self.backbone.classifier = nn.Identity()
        
        # Attention mechanism
        self.attention = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(num_features, num_features // 4),
            nn.ReLU(),
            nn.Linear(num_features // 4, num_features),
            nn.Sigmoid()
        )
        
        # Custom classifier head
        self.classifier = nn.Sequential(
            nn.Dropout(dropout_rate),
            nn.Linear(num_features, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.5),
            nn.Linear(512, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.3),
            nn.Linear(256, num_classes)
        )
    
    def forward(self, x):
        features = self.backbone.features(x)
        pooled = F.adaptive_avg_pool2d(features, 1)
        pooled = torch.flatten(pooled, 1)
        attention_weights = self.attention(features)
        attended_features = pooled * attention_weights
        output = self.classifier(attended_features)
        return output

# Télécharger les fichiers depuis HuggingFace
print("📥 Téléchargement du modèle...")
model_path = hf_hub_download(repo_id="Abuzaid01/plant-disease-classifier", filename="model.pth")
config_path = hf_hub_download(repo_id="Abuzaid01/plant-disease-classifier", filename="config.json")

# Charger la configuration
with open(config_path, 'r') as f:
    config = json.load(f)

print(f"📊 Classes: {config['num_classes']}")
print(f"📋 Labels: {config['class_names']}")

# Charger le checkpoint
print("⚙️ Chargement du checkpoint...")
checkpoint = torch.load(model_path, map_location='cpu')

# Créer le modèle avec l'architecture correcte
print("🔧 Création du modèle PlantDiseaseClassifier...")
model = PlantDiseaseClassifier(num_classes=config['num_classes'], dropout_rate=0.3)

# Charger les poids
state_dict = checkpoint.get('model_state_dict', checkpoint)
result = model.load_state_dict(state_dict, strict=False)

print(f"✅ Modèle chargé!")
print(f"   📊 Poids chargés: {len(state_dict)}")
if result.missing_keys:
    print(f"   ⚠️  Clés manquantes: {len(result.missing_keys)}")
if result.unexpected_keys:
    print(f"   ⚠️  Clés inattendues: {len(result.unexpected_keys)}")

if 'training_info' in checkpoint:
    print(f"\n📈 Performance d'entraînement:")
    if 'best_val_acc' in checkpoint['training_info']:
        print(f"   Accuracy validation: {checkpoint['training_info']['best_val_acc']:.2f}%")
    if 'total_epochs' in checkpoint['training_info']:
        print(f"   Epochs: {checkpoint['training_info']['total_epochs']}")

model.eval()

# Prétraitement d'image
transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# Charger et transformer l'image
print("\n🖼️ Traitement de l'image...")
image = Image.open("plant.jpg").convert('RGB')
inputs = transform(image).unsqueeze(0)

# Prédiction
with torch.no_grad():
    outputs = model(inputs)
    probabilities = torch.nn.functional.softmax(outputs, dim=1)
    top5_prob, top5_idx = torch.topk(probabilities, k=min(5, config['num_classes']))
    
    prediction = top5_idx[0][0].item()
    confidence = top5_prob[0][0].item()

print(f"\n🎯 Résultat:")
print(f"   Classe prédite: {config['class_names'][prediction]}")
print(f"   Confiance: {confidence*100:.2f}%")
print(f"\n📊 Top 5:")
for i in range(min(5, config['num_classes'])):
    idx = top5_idx[0][i].item()
    prob = top5_prob[0][i].item()
    print(f"   {i+1}. {config['class_names'][idx]}: {prob*100:.2f}%")

# Prédiction
with torch.no_grad():
    outputs = model(inputs)
    probabilities = F.softmax(outputs, dim=1)
    top5_prob, top5_idx = torch.topk(probabilities, k=min(5, config['num_classes']))
    
    prediction = top5_idx[0][0].item()
    confidence = top5_prob[0][0].item()

print(f"\n🎯 Résultat:")
print(f"   Classe prédite: {config['class_names'][prediction]}")
print(f"   Confiance: {confidence*100:.2f}%")

print(f"\n📊 Top 5 prédictions:")
for i in range(min(5, config['num_classes'])):
    idx = top5_idx[0][i].item()
    prob = top5_prob[0][i].item()
    bar = '█' * int(prob * 20)
    print(f"   {i+1}. {config['class_names'][idx]:<30} {prob*100:>6.2f}% {bar}")