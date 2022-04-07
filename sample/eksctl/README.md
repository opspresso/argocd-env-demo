# eksctl

## eks-demo-ipv6

### cluster

```bash
eksctl create cluster -f eks-demo-ipv6.yaml

eksctl delete cluster eks-demo-ipv6
```

### addons

```bash
eksctl utils update-kube-proxy --cluster=eks-demo-ipv6
eksctl utils update-aws-node --cluster=eks-demo-ipv6
eksctl utils update-coredns --cluster=eks-demo-ipv6
```
